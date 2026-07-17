"""OSHA log + form endpoints for IR Incidents.

Covers:
- OSHA 300 log (recordable injury/illness log) + CSV
- OSHA 301 form (per-incident detail)
- OSHA 300A annual summary + CSV
- Recordability update (manual)
- Recordability AI determination (Gemini-backed)
"""
import csv
import io
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.config import get_settings
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    Osha300LogEntry,
    Osha300ASummary,
    Osha300ASaveRequest,
    OshaPrivacyCaseEntry,
    OshaRecordabilityUpdate,
    ItaCredentialUpdate,
    ItaCredentialStatus,
    ItaSubmitRequest,
    ItaSubmitResponse,
    ItaSubmission,
    ItaSubmissionListResponse,
)
from ._shared import (
    log_audit,
    _hydrate_involved_employees,
    fetch_osha_case_rows,
    fetch_osha_case_rows_for,
)
from app.core.services.osha_redaction import redact_osha_text
from app.core.services.osha_privacy import (
    determine_privacy_case,
    compose_clinical_description,
    PRIVACY_NAME,
    PRIVACY_DESCRIPTION_PLACEHOLDER,
)
from app.core.services.genai_client import get_genai_client
from app.matcha.services.naics_titles import naics_industry_description

logger = logging.getLogger(__name__)

router = APIRouter()


VALID_OSHA_CLASSIFICATIONS = {
    "death", "days_away", "restricted_duty",
    "medical_treatment", "loss_of_consciousness", "significant_injury",
}

# OSHA ITA "Establishment and Summary" CSV header tokens, in upload order.
# Exact casing/underscores matter — the ITA validator rejects any deviation.
# (Confirm against the live OSHA ITA data dictionary before a production filing;
# the box→column G–M6 mapping is stable, only header strings could drift.)
ITA_CSV_COLUMNS = [
    "ein", "company_name", "establishment_name", "street_address", "city",
    "state", "zip_code", "naics_code", "industry_description", "size",
    "establishment_type", "year_filing_for", "annual_average_employees",
    "total_hours_worked", "no_injuries_illnesses", "total_deaths",
    "total_dafw_cases", "total_djtr_cases", "total_other_cases",
    "total_dafw_days", "total_djtr_days", "total_injuries",
    "total_skin_disorders", "total_respiratory_conditions", "total_poisonings",
    "total_hearing_loss", "total_other_illnesses",
]


# Single definition of the OSHA size bands, shared with the direct-filing path —
# the CSV export and the API submission must never disagree on the size code.
# Same reason for the EIN/zip normalizers: the pre-flight validator must judge
# the exact digits the API payload will carry, not the raw stored string.
from app.matcha.services.ir_ita_submission import (  # noqa: E402
    ita_size_category as _ita_size_category,
    _normalize_ein,
    _normalize_zip,
)


# Mandatory ITA fields that can realistically be missing (city/state/zipcode are
# NOT NULL on business_locations; address/ein/naics/hours are the gaps).
def _missing_ita_fields(est: dict) -> list[str]:
    """Return the list of required ITA fields absent from an establishment dict.

    Pure (no DB) so it can be unit-tested. `est` carries the EIN/NAICS already
    resolved with company-level fallback, plus the address parts + hours/headcount.
    Mirrors what the ITA API requires to CREATE an establishment + 300A (data
    dictionary), so a filer sees the gap in the pre-flight checklist rather than
    as an OSHA rejection mid-submission. `ein` is kept required here for hygiene
    even though the API itself treats it as optional.

    Presence alone is not enough: OSHA field-validates EIN ("must be 9 digits")
    and zip ("must contain 5 or 9 digits") and rejects the whole batch when either
    is malformed. A present-but-invalid value passed this check silently and
    surfaced only as an opaque OSHA rejection at submit time, so the two are
    length-checked here on the same digits the payload builder sends.
    """
    missing = []
    # Required to create the establishment (address parts + naics + ein).
    for field in ("ein", "naics", "street_address", "city", "state", "zip_code"):
        val = est.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    # Present but malformed — OSHA rejects these, so they block the filing too.
    if "ein" not in missing and len(_normalize_ein(est.get("ein"))) != 9:
        missing.append("ein_invalid")
    if "zip_code" not in missing and len(_normalize_zip(est.get("zip_code"))) not in (5, 9):
        missing.append("zip_code_invalid")
    # Required on the 300A summary: both must be present AND > 0 (API validation).
    if not (est.get("total_hours_worked") or 0) > 0:
        missing.append("total_hours_worked")
    if not (est.get("annual_average_employees") or 0) > 0:
        missing.append("annual_average_employees")
    return missing


def _safe_json_loads(val, default=None):
    """Parse a JSON string or return a dict/list as-is."""
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default


# Non-privacy incidents with no structured injury data still must NOT show the
# raw reporter narrative (it can name patients / third parties). Show a neutral
# pointer instead — the full narrative lives only on the internal incident record.
_NO_STRUCTURED_DESCRIPTION = "See incident record for details"


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


def _mask_from_reason(privacy_case_reason, category_data: dict, osha_injury_type):
    """Hybrid Column-B mask decision for one case, from its privacy answer.

    The per-employee answer (``ir_osha_case_details.privacy_case_reason``, or the
    legacy ``category_data.privacy_cases`` value for un-captured rows) is the
    source of truth:
      * a reason string  → mask (human confirmed this category),
      * ``"none"``        → don't mask (human reviewed and cleared it),
      * NULL/unanswered   → fall back to ``determine_privacy_case`` as a
        fail-closed safety net (incident-level signals + this case's M-column
        injury type; may over-mask, the safe direction).
    Returns ``(is_privacy_case, reason)``.
    """
    if isinstance(privacy_case_reason, str):
        h = privacy_case_reason.strip().lower()
        if h == "none":
            return False, None
        if h:
            return True, h
    cd = category_data or {}
    return determine_privacy_case(
        cd, osha_injury_type, bool(cd.get("employee_privacy_requested")),
    )


def _resolve_osha_description(category_data: dict, is_privacy_case: bool) -> str:
    """OSHA 300/301 Description (Column F) — NEVER the raw reporter narrative.

    Precedence (all name-free by construction):
      1. ``osha_clean_description`` — the AI-cleansed narrative (names stripped).
      2. ``compose_clinical_description`` — structured injury phrase.
      3. a neutral placeholder.
    """
    cd = category_data or {}
    clean = (cd.get("osha_clean_description") or "").strip()
    if clean:
        return clean
    return compose_clinical_description(cd) or (
        PRIVACY_DESCRIPTION_PLACEHOLDER if is_privacy_case else _NO_STRUCTURED_DESCRIPTION
    )


def _reporter_name_title(row):
    """``(name, job_title)`` for the reporter-fallback case — the reporter's
    roster match if any, else the typed ``reported_by_name``."""
    name = row["reported_by_name"]
    if row.get("emp_first_name"):
        name = f"{row['emp_first_name']} {row.get('emp_last_name') or ''}".strip()
    return name, row.get("emp_job_title")


def _injured_persons(row, emp_map: dict) -> list:
    """One injured person per row: ``[(case_key, name, job_title)]`` — the
    incident-level fallback when an incident has no ir_osha_case_details rows.

    Roster employees from ``involved_employee_ids`` (name + Finch-synced
    ``job_title``), in stored order; else a single ``"reporter"`` row.
    """
    ids = [str(x) for x in (row.get("involved_employee_ids") or []) if x]
    if ids:
        out = []
        for eid in ids:
            emp = emp_map.get(eid)
            if emp:
                name = f"{emp.get('first_name') or ''} {emp.get('last_name') or ''}".strip() or "Unknown"
                out.append((eid, name, emp.get("job_title")))
            else:
                # id no longer on the roster — keep a row (mask-safe), no name leak.
                out.append((eid, "Unknown", None))
        return out
    name, title = _reporter_name_title(row)
    return [("reporter", name, title)]


def _osha_case_views(row, case_rows, emp_map) -> list:
    """Per-incident case views for the 300/301 reads — one per injured employee.

    Each view: ``{case_key, case_seq, name, job_title, classification,
    days_away, days_restricted, injury_type, privacy_case_reason}``. Prefers the
    ``ir_osha_case_details`` rows (per-employee classification/days/injury +
    privacy); falls back to synthesizing from the incident-level columns +
    ``involved_employee_ids`` + ``category_data.privacy_cases`` when an incident
    has no case rows yet (legacy / not-yet-captured).
    """
    if case_rows:
        views = []
        for cr in case_rows:  # ordered by case_seq
            ek = cr.get("case_key")
            if ek == "reporter":
                name, title = _reporter_name_title(row)
            else:
                emp = emp_map.get(ek)
                if emp:
                    name = f"{emp.get('first_name') or ''} {emp.get('last_name') or ''}".strip() or "Unknown"
                    title = emp.get("job_title")
                else:
                    name, title = "Unknown", None
            views.append({
                "case_key": ek,
                "case_seq": cr.get("case_seq") or 1,
                "name": name,
                "job_title": title,
                "classification": cr.get("classification"),
                "days_away": cr.get("days_away") or 0,
                "days_restricted": cr.get("days_restricted") or 0,
                "injury_type": cr.get("injury_type"),
                "privacy_case_reason": cr.get("privacy_case_reason"),
            })
        return views
    # Fallback: no case rows yet — synthesize from incident-level values.
    cd = _safe_json_loads(row.get("category_data"), {})
    form_301 = _safe_json_loads(row.get("osha_form_301_data"), {})
    privacy_map = cd.get("privacy_cases") or {}
    out = []
    for idx, (key, name, title) in enumerate(_injured_persons(row, emp_map)):
        out.append({
            "case_key": key,
            "case_seq": idx + 1,
            "name": name,
            "job_title": title,
            "classification": row.get("osha_classification"),
            "days_away": row.get("days_away_from_work") or 0,
            "days_restricted": row.get("days_restricted_duty") or 0,
            "injury_type": form_301.get("injury_type"),
            "privacy_case_reason": privacy_map.get(key),
        })
    return out


async def _hydrate_case_emp_map(conn, company_id, rows, cases_by_incident) -> dict:
    """Batch-resolve employee ids → roster detail for the 300-log read. Gathers
    ids from case rows' ``employee_id`` (captured incidents) and from
    ``involved_employee_ids`` (fallback incidents). One query."""
    emp_ids = set()
    for row in rows:
        crs = cases_by_incident.get(str(row["id"]))
        if crs:
            for cr in crs:
                if cr.get("employee_id"):
                    emp_ids.add(str(cr["employee_id"]))
        else:
            for x in (row.get("involved_employee_ids") or []):
                if x:
                    emp_ids.add(str(x))
    if not emp_ids:
        return {}
    hydrated = await _hydrate_involved_employees(conn, company_id, list(emp_ids))
    return {str(e["id"]): e for e in hydrated}


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


async def _osha_data_quality_warnings(conn, company_id, year, location_id=None) -> list[str]:
    """Non-blocking data-quality flags for a 300A / ITA filing.

    - When ``location_id`` is given: recordable incidents at that establishment/year
      whose classification is missing (they foot into "other recordable" but lack
      the death/days-away/restricted detail the 300A/301 needs).
    - Always: recordable incidents in the year that are NOT assigned to any
      location. These appear on the company-wide 300 log but on NO 300A summary
      and in NO ITA row, so they are silently excluded from the actual filing.
    """
    warnings: list[str] = []

    if location_id is not None:
        missing_class = await conn.fetchval(
            """
            SELECT COUNT(*) FROM ir_incidents i
            WHERE i.company_id = $1
              AND i.location_id = $2
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $3
              AND NOT EXISTS (
                  SELECT 1 FROM ir_osha_case_details cd
                  WHERE cd.incident_id = i.id AND cd.classification IS NOT NULL
              )
              AND i.osha_classification IS NULL
            """,
            company_id, location_id, year,
        ) or 0
        if missing_class:
            warnings.append(
                f"{missing_class} recordable incident(s) at this establishment have no "
                f"OSHA classification (death / days away / restricted / other). They are "
                f"counted but cannot be placed in columns G–J correctly until classified."
            )

    unassigned = await conn.fetchval(
        """
        SELECT COUNT(*) FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND EXTRACT(YEAR FROM occurred_at) = $2
          AND location_id IS NULL
        """,
        company_id, year,
    ) or 0
    if unassigned:
        warnings.append(
            f"{unassigned} recordable incident(s) in {year} are not assigned to a "
            f"location and are excluded from every 300A summary and the ITA export. "
            f"Assign each to an establishment so it appears on the correct filing."
        )

    return warnings


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


async def _resolve_establishment(conn, company_id, location_id):
    """Fetch a company's location row with EIN/NAICS company-level fallback.

    Returns the asyncpg Record (location fields + resolved ein/naics) or None if
    the location does not belong to the company (caller raises 404).
    """
    return await conn.fetchrow(
        """
        SELECT
            bl.id, bl.name, bl.address, bl.city, bl.state, bl.zipcode,
            COALESCE(bl.ein, c.ein) AS ein,
            COALESCE(bl.naics, c.naics) AS naics,
            c.executive_name, c.executive_title, c.executive_phone
        FROM business_locations bl
        JOIN companies c ON c.id = bl.company_id
        WHERE bl.id = $1 AND bl.company_id = $2
        """,
        location_id, company_id,
    )


@router.get("/osha/300-log", response_model=list[Osha300LogEntry])
async def get_osha_300_log(
    year: int = Query(..., description="Calendar year for the 300 log"),
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 300 log for a given year."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.id,
                i.osha_case_number,
                i.title,
                i.description,
                i.location,
                i.occurred_at,
                i.osha_classification,
                COALESCE(i.days_away_from_work, 0) AS days_away_from_work,
                COALESCE(i.days_restricted_duty, 0) AS days_restricted_duty,
                i.category_data,
                i.osha_form_301_data,
                i.involved_employee_ids,
                i.reported_by_name,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title
            FROM ir_incidents i
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id = i.company_id
            WHERE i.company_id = $1
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $2
            ORDER BY i.occurred_at
            """,
            company_id,
            year,
        )
        cases_by_incident = await fetch_osha_case_rows_for(conn, [r["id"] for r in rows])
        emp_map = await _hydrate_case_emp_map(conn, company_id, rows, cases_by_incident)

    entries = []
    for row in rows:
        category_data = _safe_json_loads(row.get("category_data"), {})
        injury_type_display = category_data.get("injury_type")  # clinical nature, incident-level
        base_case = row["osha_case_number"] or str(row["id"])[:8]
        date_str = row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else ""
        location = redact_osha_text(row["location"])

        # One row per injured employee — each its OWN classification/days/injury
        # (from its ir_osha_case_details row, incident-level fallback otherwise)
        # and its OWN Column-B mask. Description (Column F) is name-free regardless.
        views = _osha_case_views(row, cases_by_incident.get(str(row["id"]), []), emp_map)
        multi = len(views) > 1
        for v in views:
            is_priv, reason = _mask_from_reason(v["privacy_case_reason"], category_data, v["injury_type"])
            entries.append(Osha300LogEntry(
                case_number=f"{base_case}-{v['case_seq']}" if multi else base_case,
                employee_name=PRIVACY_NAME if is_priv else v["name"],
                job_title=v["job_title"],
                date_of_injury=date_str,
                location=location,
                description=_resolve_osha_description(category_data, is_priv),
                classification=v["classification"],
                days_away=v["days_away"],
                days_restricted=v["days_restricted"],
                injury_type=injury_type_display,
                incident_id=str(row["id"]),
                is_privacy_case=is_priv,
                privacy_case_reason=reason,
            ))
    return entries


@router.get("/osha/300-log/csv")
async def get_osha_300_log_csv(
    year: int = Query(..., description="Calendar year for the 300 log CSV"),
    attested: bool = Query(False, description="Reviewer confirmed they reviewed the data before export"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300 log as CSV for a given year."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        await _attest_export(conn, current_user, form="300_log", year=year, attested=attested)

    entries = await get_osha_300_log(year=year, current_user=current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Case Number", "Employee Name", "Job Title", "Date of Injury/Illness",
        "Where Event Occurred", "Description", "Classification",
        "Days Away From Work", "Days on Restricted Duty", "Injury/Illness Type",
        "Incident ID",
    ])
    for entry in entries:
        writer.writerow([
            entry.case_number,
            entry.employee_name,
            entry.job_title or "",
            entry.date_of_injury,
            entry.location or "",
            entry.description or "",
            entry.classification or "",
            entry.days_away,
            entry.days_restricted,
            entry.injury_type or "",
            entry.incident_id,
        ])

    output.seek(0)
    filename = f"osha_300_log_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/osha/privacy-cases", response_model=list[OshaPrivacyCaseEntry])
async def get_osha_privacy_cases(
    year: int = Query(..., description="Calendar year for the privacy-case reference list"),
    current_user=Depends(require_admin_or_client),
):
    """Confidential OSHA Privacy Case reference list (29 CFR 1904.29(b)(9)).

    Resolves each masked 300-log row's case number back to the REAL employee
    name. Company-scoped, admin/client-gated, and every access is written to the
    IR audit log. Never exposed on the public 300 log / CSV / 301 form.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.id,
                i.osha_case_number,
                i.occurred_at,
                i.osha_classification,
                i.category_data,
                i.osha_form_301_data,
                i.involved_employee_ids,
                i.reported_by_name,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title
            FROM ir_incidents i
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id = i.company_id
            WHERE i.company_id = $1
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $2
            ORDER BY i.occurred_at
            """,
            company_id,
            year,
        )
        cases_by_incident = await fetch_osha_case_rows_for(conn, [r["id"] for r in rows])
        emp_map = await _hydrate_case_emp_map(conn, company_id, rows, cases_by_incident)

        entries: list[OshaPrivacyCaseEntry] = []
        for row in rows:
            category_data = _safe_json_loads(row.get("category_data"), {})
            base_case = row["osha_case_number"] or str(row["id"])[:8]
            views = _osha_case_views(row, cases_by_incident.get(str(row["id"]), []), emp_map)
            multi = len(views) > 1
            for v in views:
                is_priv, reason = _mask_from_reason(v["privacy_case_reason"], category_data, v["injury_type"])
                if not is_priv:
                    continue
                entries.append(OshaPrivacyCaseEntry(
                    case_number=f"{base_case}-{v['case_seq']}" if multi else base_case,
                    real_employee_name=v["name"] or "Unknown",
                    privacy_case_reason=reason,
                    classification=v["classification"],
                    date_of_injury=row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else "",
                    incident_id=str(row["id"]),
                ))

        # Confidential access is audited (list view → no single-incident scope).
        await log_audit(
            conn, None, str(current_user.id), "privacy_case_names_viewed",
            entity_type="osha_privacy_case",
            details={"year": year, "count": len(entries)},
        )

    return entries


@router.get("/osha/301/{incident_id}")
async def get_osha_301_form(
    incident_id: UUID,
    employee_id: Optional[UUID] = Query(None, description="Which injured employee's 301 (defaults to the first injured person)"),
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 301 form data for a recordable incident + injured employee."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                i.*,
                c.name AS company_name,
                c.address AS company_address,
                bl.name AS location_name,
                bl.city AS location_city,
                bl.state AS location_state,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title,
                e.personal_email AS emp_email,
                e.start_date AS emp_start_date
            FROM ir_incidents i
            LEFT JOIN companies c ON c.id = i.company_id
            LEFT JOIN business_locations bl ON bl.id = i.location_id
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id = i.company_id
            WHERE i.id = $1
              AND i.company_id = $2
              AND i.osha_recordable = true
            """,
            incident_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Recordable incident not found")
        case_rows = await fetch_osha_case_rows(conn, row["id"])
        emp_map = await _hydrate_case_emp_map(
            conn, company_id, [row], {str(row["id"]): case_rows}
        )

    category_data = _safe_json_loads(row.get("category_data"), {})
    form_301_data = _safe_json_loads(row.get("osha_form_301_data"), {})

    # One 301 per injured employee. Pick the requested employee (else the first
    # injured person) and key the mask + facts to that person's case so the 301
    # matches its 300-log row. Description is name-free (never the raw narrative).
    # The real name stays resolvable via /osha/privacy-cases.
    views = _osha_case_views(row, case_rows, emp_map)
    target = None
    if employee_id is not None:
        target = next((v for v in views if v["case_key"] == str(employee_id)), None)
    if target is None:
        target = views[0]
    is_reporter = target["case_key"] == "reporter"
    base_case = row["osha_case_number"] or str(row["id"])[:8]
    case_number = f"{base_case}-{target['case_seq']}" if len(views) > 1 else base_case

    is_priv, reason = _mask_from_reason(target["privacy_case_reason"], category_data, target["injury_type"])
    clinical_description = _resolve_osha_description(category_data, is_priv)
    return {
        "incident_id": str(row["id"]),
        "case_number": case_number,
        "employee_name": PRIVACY_NAME if is_priv else target["name"],
        "is_privacy_case": is_priv,
        "privacy_case_reason": reason,
        # email/start_date come from the reporter join — valid only when this 301
        # is the reporter's own; otherwise it would show another person's PII.
        "employee_email": row.get("emp_email") if is_reporter else None,
        "employee_job_title": target["job_title"],
        "employee_start_date": row["emp_start_date"].isoformat() if (is_reporter and row.get("emp_start_date")) else None,
        "employer_name": row.get("company_name"),
        "employer_address": row.get("company_address"),
        "establishment_name": row.get("location_name"),
        "establishment_city": row.get("location_city"),
        "establishment_state": row.get("location_state"),
        "date_of_injury": row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else None,
        "time_of_event": row["occurred_at"].strftime("%H:%M") if row["occurred_at"] else None,
        "location_of_event": redact_osha_text(row.get("location")),
        "description_of_injury": clinical_description,
        "object_or_substance": category_data.get("equipment_involved"),
        "injury_type": category_data.get("injury_type"),
        "body_parts_affected": category_data.get("body_parts", []),
        "treatment": redact_osha_text(category_data.get("treatment")),
        "osha_classification": target["classification"],
        "days_away_from_work": target["days_away"],
        "days_restricted_duty": target["days_restricted"],
        "date_of_death": row["date_of_death"].isoformat() if row.get("date_of_death") else None,
        "additional_data": form_301_data,
    }


@router.get("/osha/300a", response_model=Osha300ASummary)
async def get_osha_300a_summary(
    year: int = Query(..., description="Calendar year for the 300A summary"),
    location_id: UUID = Query(..., description="business_locations.id — 300A is per establishment"),
    current_user=Depends(require_admin_or_client),
):
    """Generate the per-establishment OSHA 300A annual summary for a given year.

    Strict per-establishment: requires a location_id, and 400s if the company has
    no active locations. average_employees auto-computes from the active roster at
    the location (overridable via the saved row); total_hours_worked is manual.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        loc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM business_locations WHERE company_id = $1 AND is_active = true",
            company_id,
        )
        if not loc_count:
            raise HTTPException(
                status_code=400,
                detail="No business locations defined. OSHA 300A summaries are per "
                       "establishment — add at least one location first.",
            )

        est = await _resolve_establishment(conn, company_id, location_id)
        if est is None:
            raise HTTPException(status_code=404, detail="Location not found")

        auto_headcount = await _active_headcount(
            conn, company_id, location_id,
            city=est["city"], state=est["state"], sole_location=(loc_count == 1),
        )
        agg = await _aggregate_300a(conn, company_id, location_id, year)
        warnings = await _osha_data_quality_warnings(conn, company_id, year, location_id)

        cached = await conn.fetchrow(
            "SELECT * FROM osha_annual_summaries WHERE company_id = $1 AND location_id = $2 AND year = $3",
            company_id, location_id, year,
        )

        return Osha300ASummary(
            year=year,
            establishment_name=est["name"],
            establishment_id=str(est["id"]),
            ein=est["ein"],
            naics=est["naics"],
            industry_description=naics_industry_description(est["naics"]),
            address=est["address"],
            city=est["city"],
            state=est["state"],
            zipcode=est["zipcode"],
            executive_name=est["executive_name"],
            executive_title=est["executive_title"],
            executive_phone=est["executive_phone"],
            total_cases=agg["total_cases"],
            total_deaths=agg["total_deaths"],
            total_days_away_cases=agg["total_days_away_cases"],
            total_restricted_cases=agg["total_restricted_cases"],
            total_other_recordable=agg["total_other_recordable"],
            total_days_away=agg["total_days_away"],
            total_days_restricted=agg["total_days_restricted"],
            total_injuries=agg["total_injuries"],
            total_skin_disorders=agg["total_skin_disorders"],
            total_respiratory=agg["total_respiratory"],
            total_poisonings=agg["total_poisonings"],
            total_hearing_loss=agg["total_hearing_loss"],
            total_other_illnesses=agg["total_other_illnesses"],
            # Saved override wins; else the live roster count.
            average_employees=(cached["average_employees"] if cached and cached["average_employees"] is not None else auto_headcount),
            total_hours_worked=cached["total_hours_worked"] if cached else None,
            certified_by=cached["certified_by"] if cached else None,
            certified_title=cached["certified_title"] if cached else None,
            certified_date=cached["certified_date"] if cached else None,
            data_quality_warnings=warnings,
        )


@router.put("/osha/300a/save")
async def save_osha_300a(
    body: Osha300ASaveRequest,
    current_user=Depends(require_admin_or_client),
):
    """Upsert manual hours / headcount override / certification for a 300A.

    Recomputes the total_* counts server-side so the persisted snapshot is
    consistent with the recordable incidents at the establishment.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        est = await _resolve_establishment(conn, company_id, body.location_id)
        if est is None:
            raise HTTPException(status_code=404, detail="Location not found")

        agg = await _aggregate_300a(conn, company_id, body.location_id, body.year)
        avg_emp = body.average_employees
        if avg_emp is None:
            loc_count = await conn.fetchval(
                "SELECT COUNT(*) FROM business_locations WHERE company_id = $1 AND is_active = true",
                company_id,
            )
            avg_emp = await _active_headcount(
                conn, company_id, body.location_id,
                city=est["city"], state=est["state"], sole_location=(loc_count == 1),
            )

        await conn.execute(
            """
            INSERT INTO osha_annual_summaries (
                company_id, location_id, year, establishment_name,
                total_cases, total_deaths, total_days_away_cases, total_restricted_cases,
                total_other_recordable, total_days_away, total_days_restricted,
                total_injuries, total_skin_disorders, total_respiratory, total_poisonings,
                total_hearing_loss, total_other_illnesses,
                average_employees, total_hours_worked,
                certified_by, certified_title, certified_date
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7, $8,
                $9, $10, $11,
                $12, $13, $14, $15,
                $16, $17,
                $18, $19,
                $20, $21, $22
            )
            ON CONFLICT (company_id, COALESCE(location_id, '00000000-0000-0000-0000-000000000000'::uuid), year)
            DO UPDATE SET
                establishment_name = EXCLUDED.establishment_name,
                total_cases = EXCLUDED.total_cases,
                total_deaths = EXCLUDED.total_deaths,
                total_days_away_cases = EXCLUDED.total_days_away_cases,
                total_restricted_cases = EXCLUDED.total_restricted_cases,
                total_other_recordable = EXCLUDED.total_other_recordable,
                total_days_away = EXCLUDED.total_days_away,
                total_days_restricted = EXCLUDED.total_days_restricted,
                total_injuries = EXCLUDED.total_injuries,
                total_skin_disorders = EXCLUDED.total_skin_disorders,
                total_respiratory = EXCLUDED.total_respiratory,
                total_poisonings = EXCLUDED.total_poisonings,
                total_hearing_loss = EXCLUDED.total_hearing_loss,
                total_other_illnesses = EXCLUDED.total_other_illnesses,
                average_employees = EXCLUDED.average_employees,
                total_hours_worked = EXCLUDED.total_hours_worked,
                certified_by = EXCLUDED.certified_by,
                certified_title = EXCLUDED.certified_title,
                certified_date = EXCLUDED.certified_date
            """,
            company_id, body.location_id, body.year, est["name"],
            agg["total_cases"], agg["total_deaths"], agg["total_days_away_cases"], agg["total_restricted_cases"],
            agg["total_other_recordable"], agg["total_days_away"], agg["total_days_restricted"],
            agg["total_injuries"], agg["total_skin_disorders"], agg["total_respiratory"], agg["total_poisonings"],
            agg["total_hearing_loss"], agg["total_other_illnesses"],
            avg_emp, body.total_hours_worked,
            body.certified_by, body.certified_title, body.certified_date,
        )

        await log_audit(
            conn, None, str(current_user.id), "osha_300a_saved",
            entity_type="osha_annual_summary", entity_id=str(body.location_id),
            details={"year": body.year},
        )

    return {"message": "OSHA 300A summary saved", "location_id": str(body.location_id), "year": body.year}


@router.get("/osha/300a/pdf")
async def get_osha_300a_pdf(
    year: int = Query(..., description="Calendar year for the 300A PDF"),
    location_id: UUID = Query(..., description="business_locations.id — 300A is per establishment"),
    attested: bool = Query(False, description="Reviewer confirmed they reviewed the data before export"),
    current_user=Depends(require_admin_or_client),
):
    """Render the faithful federal OSHA Form 300A as a PDF for one establishment."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        await _attest_export(conn, current_user, form="300a_pdf", year=year, attested=attested, location_id=location_id)

    summary = await get_osha_300a_summary(year=year, location_id=location_id, current_user=current_user)
    from ._osha_pdf import render_300a_pdf
    pdf_bytes = await render_300a_pdf(summary.model_dump())
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="osha_300a_{year}.pdf"'},
    )


@router.get("/osha/300a/csv")
async def get_osha_300a_csv(
    year: int = Query(..., description="Calendar year for the 300A summary CSV"),
    location_id: UUID = Query(..., description="business_locations.id — 300A is per establishment"),
    attested: bool = Query(False, description="Reviewer confirmed they reviewed the data before export"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300A annual summary as CSV."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        await _attest_export(conn, current_user, form="300a_csv", year=year, attested=attested, location_id=location_id)

    summary = await get_osha_300a_summary(year=year, location_id=location_id, current_user=current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Field", "Value"])
    writer.writerow(["Year", summary.year])
    writer.writerow(["Establishment Name", summary.establishment_name or ""])
    writer.writerow(["Total Cases", summary.total_cases])
    writer.writerow(["Total Deaths", summary.total_deaths])
    writer.writerow(["Total Days Away From Work Cases", summary.total_days_away_cases])
    writer.writerow(["Total Restricted Duty / Transfer Cases", summary.total_restricted_cases])
    writer.writerow(["Total Other Recordable Cases", summary.total_other_recordable])
    writer.writerow(["Total Days Away From Work", summary.total_days_away])
    writer.writerow(["Total Days Restricted Duty", summary.total_days_restricted])
    writer.writerow(["Total Injuries", summary.total_injuries])
    writer.writerow(["Total Skin Disorders", summary.total_skin_disorders])
    writer.writerow(["Total Respiratory Conditions", summary.total_respiratory])
    writer.writerow(["Total Poisonings", summary.total_poisonings])
    writer.writerow(["Total Hearing Loss", summary.total_hearing_loss])
    writer.writerow(["Total Other Illnesses", summary.total_other_illnesses])
    writer.writerow(["Average Number of Employees", summary.average_employees or ""])
    writer.writerow(["Total Hours Worked", summary.total_hours_worked or ""])

    output.seek(0)
    filename = f"osha_300a_summary_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _gather_ita_establishments(conn, company_id, year) -> list[dict]:
    """Build one ITA row dict per active establishment for the year.

    Each dict carries the resolved identity (EIN/NAICS with company fallback),
    the manual hours + headcount from the saved summary row (auto headcount when
    unsaved), and the recomputed 300A totals. Shared by validate + export.
    """
    company = await conn.fetchrow(
        "SELECT COALESCE(legal_name, name) AS company_name FROM companies WHERE id = $1",
        company_id,
    )
    company_name = company["company_name"] if company else ""

    locations = await conn.fetch(
        """
        SELECT bl.id, bl.name, bl.address, bl.city, bl.state, bl.zipcode,
               COALESCE(bl.ein, c.ein) AS ein,
               COALESCE(bl.naics, c.naics) AS naics
        FROM business_locations bl
        JOIN companies c ON c.id = bl.company_id
        WHERE bl.company_id = $1 AND bl.is_active = true
        ORDER BY bl.name
        """,
        company_id,
    )

    sole = len(locations) == 1
    rows = []
    for loc in locations:
        agg = await _aggregate_300a(conn, company_id, loc["id"], year)
        saved = await conn.fetchrow(
            "SELECT average_employees, total_hours_worked FROM osha_annual_summaries "
            "WHERE company_id = $1 AND location_id = $2 AND year = $3",
            company_id, loc["id"], year,
        )
        avg_emp = saved["average_employees"] if saved and saved["average_employees"] is not None else \
            await _active_headcount(
                conn, company_id, loc["id"],
                city=loc["city"], state=loc["state"], sole_location=sole,
            )
        hours = saved["total_hours_worked"] if saved else None

        rows.append({
            "location_id": str(loc["id"]),
            "establishment_name": loc["name"] or "",
            "company_name": company_name,
            "ein": loc["ein"],
            "naics": loc["naics"],
            "street_address": loc["address"],
            "city": loc["city"],
            "state": loc["state"],
            "zip_code": loc["zipcode"],
            "annual_average_employees": avg_emp,
            "total_hours_worked": hours,
            "agg": agg,
        })
    return rows


@router.get("/osha/ita/validate")
async def validate_ita_export(
    year: int = Query(..., description="Calendar year to validate for ITA filing"),
    current_user=Depends(require_admin_or_client),
):
    """Pre-flight: list establishments missing required ITA fields (EIN/NAICS/etc.).

    Returns [] when every active establishment is filing-ready. Lets the UI show
    a checklist without triggering a download attempt.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        establishments = await _gather_ita_establishments(conn, company_id, year)
        unassigned = await conn.fetchval(
            """
            SELECT COUNT(*) FROM ir_incidents
            WHERE company_id = $1
              AND osha_recordable = true
              AND EXTRACT(YEAR FROM occurred_at) = $2
              AND location_id IS NULL
            """,
            company_id, year,
        ) or 0

    problems = []
    for est in establishments:
        missing = _missing_ita_fields(est)
        if missing:
            problems.append({
                "location_id": est["location_id"],
                "establishment_name": est["establishment_name"],
                "missing": missing,
            })
    # Completeness pre-flight: recordables not tied to any establishment are
    # excluded from the ITA export entirely (they only show on the company-wide
    # 300 log). Surface them as a company-level, non-blocking problem entry so
    # the reviewer can't miss that N cases won't be filed. location_id is None
    # to distinguish it from a per-establishment missing-fields row.
    if unassigned:
        problems.append({
            "location_id": None,
            "establishment_name": f"{unassigned} unassigned recordable incident(s)",
            "missing": ["unassigned_location"],
        })
    return problems


@router.get("/osha/ita/export.csv")
async def export_ita_csv(
    year: int = Query(..., description="Calendar year for the ITA bulk export"),
    attested: bool = Query(False, description="Reviewer confirmed they reviewed the data before export"),
    current_user=Depends(require_admin_or_client),
):
    """Master ITA Establishment-and-Summary CSV — one row per establishment.

    Validates mandatory fields first; returns 400 with a structured list of
    offending establishments before streaming anything.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        await _attest_export(conn, current_user, form="ita", year=year, attested=attested)
        establishments = await _gather_ita_establishments(conn, company_id, year)

    if not establishments:
        raise HTTPException(
            status_code=400,
            detail="No active business locations to file. Add at least one establishment.",
        )

    problems = []
    for est in establishments:
        missing = _missing_ita_fields(est)
        if missing:
            problems.append({
                "location_id": est["location_id"],
                "establishment_name": est["establishment_name"],
                "missing": missing,
            })
    if problems:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Cannot export ITA file — establishments are missing required fields.",
                "establishments": problems,
            },
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ITA_CSV_COLUMNS)
    writer.writeheader()
    for est in establishments:
        agg = est["agg"]
        writer.writerow({
            # Normalized to digits for the same reason the API payload is: the ITA
            # portal enforces "EIN can only contain numbers" and a 5-or-9-digit zip
            # on the uploaded file too, so a hyphenated EIN is rejected at the
            # portal instead of at submit. CSV and API must carry identical bytes.
            "ein": _normalize_ein(est["ein"]),
            "company_name": est["company_name"],
            "establishment_name": est["establishment_name"],
            "street_address": est["street_address"] or "",
            "city": est["city"] or "",
            "state": est["state"] or "",
            "zip_code": _normalize_zip(est["zip_code"]),
            "naics_code": est["naics"] or "",
            "industry_description": naics_industry_description(est["naics"]) or "",
            "size": _ita_size_category(est["annual_average_employees"]),
            "establishment_type": 1,  # 1 = private (not a government establishment)
            "year_filing_for": year,
            "annual_average_employees": est["annual_average_employees"] or 0,
            "total_hours_worked": est["total_hours_worked"] or 0,
            "no_injuries_illnesses": 1 if agg["total_cases"] == 0 else 0,
            "total_deaths": agg["total_deaths"],
            "total_dafw_cases": agg["total_days_away_cases"],
            "total_djtr_cases": agg["total_restricted_cases"],
            "total_other_cases": agg["total_other_recordable"],
            "total_dafw_days": agg["total_days_away"],
            "total_djtr_days": agg["total_days_restricted"],
            "total_injuries": agg["total_injuries"],
            "total_skin_disorders": agg["total_skin_disorders"],
            "total_respiratory_conditions": agg["total_respiratory"],
            "total_poisonings": agg["total_poisonings"],
            "total_hearing_loss": agg["total_hearing_loss"],
            "total_other_illnesses": agg["total_other_illnesses"],
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=osha_ita_{year}.csv"},
    )


@router.get("/osha/ita/credentials", response_model=ItaCredentialStatus)
async def get_ita_credentials_status(
    current_user=Depends(require_admin_or_client),
):
    """Whether an OSHA ITA API token is on file. Never returns the token."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT updated_at FROM osha_ita_credentials WHERE company_id = $1",
            company_id,
        )
    return ItaCredentialStatus(configured=row is not None, updated_at=row["updated_at"] if row else None)


@router.put("/osha/ita/credentials", response_model=ItaCredentialStatus)
async def set_ita_credentials(
    payload: ItaCredentialUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Store/replace the company's OSHA ITA API token (encrypted at rest)."""
    from app.core.services.secret_crypto import encrypt_secret

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    token = (payload.api_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="API token is required")

    encrypted = encrypt_secret(token)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO osha_ita_credentials (company_id, api_token, created_by, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (company_id) DO UPDATE
                SET api_token = EXCLUDED.api_token, updated_at = NOW()
            RETURNING updated_at
            """,
            company_id, encrypted, str(current_user.id),
        )
        # Never log the token — only that credentials were set.
        await log_audit(
            conn, None, str(current_user.id), "osha_ita_credentials_set",
            entity_type="osha_ita", entity_id=None, details=None,
        )
    return ItaCredentialStatus(configured=True, updated_at=row["updated_at"])


@router.post("/osha/ita/submit", response_model=ItaSubmitResponse)
async def submit_ita(
    payload: ItaSubmitRequest,
    current_user=Depends(require_admin_or_client),
):
    """Directly file the ITA Establishment-and-Summary batch via the OSHA API.

    Same reviewer-attestation + field-validation gates as the CSV export, then a
    single API call whose numbers are byte-identical to the validated CSV. Every
    attempt is recorded in osha_ita_submissions for an auditable filing history.
    A missing/invalid token yields a clean `not_configured` result, not a 500.

    Filing a year twice is refused with 409 unless `resubmit` is set (an amended
    filing). The check and the API call run under a per-(company, year) advisory
    lock held for the whole transaction, so a double-click can't slip two
    filings through the gap between the check and the insert.
    """
    from app.matcha.services.ir_ita_submission import submit_establishments

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    year = payload.year
    async with get_connection() as conn, conn.transaction():
        # Serialize concurrent submits for this (company, year). Held until the
        # transaction commits — i.e. across the OSHA API call and the history
        # insert — so the duplicate check below can't race a second request.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1), $2::int)",
            f"ita_submit:{company_id}", year,
        )

        if not payload.resubmit:
            prior = await conn.fetchrow(
                """
                SELECT ita_submission_id, submitted_at
                FROM osha_ita_submissions
                WHERE company_id = $1 AND year = $2
                  AND status IN ('submitted', 'accepted')
                ORDER BY submitted_at DESC
                LIMIT 1
                """,
                company_id, year,
            )
            if prior:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "already_filed",
                        "message": (
                            f"{year} has already been filed with OSHA. "
                            "Set resubmit=true to file an amended submission."
                        ),
                        "year": year,
                        "submission_id": prior["ita_submission_id"],
                        "submitted_at": prior["submitted_at"].isoformat(),
                    },
                )

        # Reviewer attestation (403 + disclaimer when not attested) — same gate
        # as every OSHA export, since this IS the filing.
        await _attest_export(conn, current_user, form="ita_submit", year=year, attested=payload.attested)

        establishments = await _gather_ita_establishments(conn, company_id, year)
        if not establishments:
            raise HTTPException(
                status_code=400,
                detail="No active business locations to file. Add at least one establishment.",
            )

        problems = []
        for est in establishments:
            missing = _missing_ita_fields(est)
            if missing:
                problems.append({
                    "location_id": est["location_id"],
                    "establishment_name": est["establishment_name"],
                    "missing": missing,
                })
        if problems:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Cannot submit ITA filing — establishments are missing required fields.",
                    "establishments": problems,
                },
            )

        token_row = await conn.fetchrow(
            "SELECT api_token FROM osha_ita_credentials WHERE company_id = $1",
            company_id,
        )
        encrypted_token = token_row["api_token"] if token_row else None

        result = await submit_establishments(
            encrypted_token, establishments, year, resubmit=payload.resubmit,
        )

        # Persist every attempt (including not_configured) for the filing history.
        # ita_submission_id is a single column: with multiple establishments we
        # store the first submission id; the full per-establishment id list +
        # trace lives in response_payload.
        row = await conn.fetchrow(
            """
            INSERT INTO osha_ita_submissions
                (company_id, location_id, year, status, ita_submission_id,
                 establishment_count, response_payload, error_detail, submitted_by)
            VALUES ($1, NULL, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            company_id, year, result.status, result.submission_id,
            len(establishments),
            json.dumps(result.response) if result.response else None,
            result.error, str(current_user.id),
        )
        await log_audit(
            conn, None, str(current_user.id), "osha_ita_submitted",
            entity_type="osha_ita_submission", entity_id=str(row["id"]),
            details={"year": year, "status": result.status,
                     "establishment_count": len(establishments)},
        )

    return ItaSubmitResponse(
        status=result.status,
        submission_id=result.submission_id,
        establishment_count=len(establishments),
        error=result.error,
    )


@router.get("/osha/ita/submissions", response_model=ItaSubmissionListResponse)
async def list_ita_submissions(
    year: Optional[int] = Query(None),
    current_user=Depends(require_admin_or_client),
):
    """ITA filing history for this company (optionally one year)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    params = [company_id]
    year_clause = ""
    if year is not None:
        params.append(year)
        year_clause = "AND year = $2"

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, location_id, year, status, ita_submission_id,
                   establishment_count, error_detail, submitted_by, submitted_at
            FROM osha_ita_submissions
            WHERE company_id = $1 {year_clause}
            ORDER BY submitted_at DESC
            LIMIT 100
            """,
            *params,
        )
    submissions = [
        ItaSubmission(
            id=r["id"],
            location_id=r["location_id"],
            year=r["year"],
            status=r["status"],
            ita_submission_id=r["ita_submission_id"],
            establishment_count=r["establishment_count"],
            error_detail=r["error_detail"],
            submitted_by=r["submitted_by"],
            submitted_at=r["submitted_at"],
        )
        for r in rows
    ]
    return ItaSubmissionListResponse(submissions=submissions, total=len(submissions))


@router.put("/{incident_id}/osha")
async def update_osha_recordability(
    incident_id: UUID,
    update: OshaRecordabilityUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Set OSHA recordability determination for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    if update.osha_classification and update.osha_classification not in VALID_OSHA_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OSHA classification. Must be one of: {', '.join(sorted(VALID_OSHA_CLASSIFICATIONS))}",
        )

    if update.wc_claim_type is not None and update.wc_claim_type not in ("acute", "cumulative_trauma", "unknown"):
        raise HTTPException(
            status_code=400,
            detail="Invalid wc_claim_type. Must be one of: acute, cumulative_trauma, unknown",
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        sets = ["osha_recordable = $3"]
        params = [str(incident_id), company_id, update.osha_recordable]
        idx = 4

        if update.osha_classification is not None:
            sets.append(f"osha_classification = ${idx}")
            params.append(update.osha_classification)
            idx += 1
        if update.osha_case_number is not None:
            sets.append(f"osha_case_number = ${idx}")
            params.append(update.osha_case_number)
            idx += 1
        if update.days_away_from_work is not None:
            sets.append(f"days_away_from_work = ${idx}")
            params.append(update.days_away_from_work)
            idx += 1
        if update.days_restricted_duty is not None:
            sets.append(f"days_restricted_duty = ${idx}")
            params.append(update.days_restricted_duty)
            idx += 1
        # WC claim depth (wcdeep01).
        if update.wc_claim_type is not None:
            sets.append(f"wc_claim_type = ${idx}")
            params.append(update.wc_claim_type)
            idx += 1
        if update.post_termination is not None:
            sets.append(f"post_termination = ${idx}")
            params.append(update.post_termination)
            idx += 1
        if update.return_to_work_date is not None:
            sets.append(f"return_to_work_date = ${idx}")
            params.append(update.return_to_work_date)
            idx += 1

        updated = await conn.fetchrow(
            f"UPDATE ir_incidents SET {', '.join(sets)} WHERE id = $1 AND company_id = $2 RETURNING *",
            *params,
        )
        # Recordability set outside the Copilot chain (manual override) still
        # needs the OSHA Privacy Case question. Emit the per-employee privacy
        # card into the transcript so it's pending next time the Copilot opens —
        # otherwise masking would fall to the safety net alone (which can't catch
        # the human-only opt-out). Idempotent + no-op if already asked/answered.
        if update.osha_recordable is True:
            from .copilot import ensure_case_chain  # lazy: avoid circular import
            await ensure_case_chain(conn, str(incident_id), current_user)
        return {"message": "OSHA recordability updated", "id": str(updated["id"])}


@router.post("/{incident_id}/osha/determine")
async def osha_ai_determination(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """AI-assisted OSHA recordability determination using Gemini."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        category_data = _safe_json_loads(row.get("category_data"), {})

        prompt = f"""Analyze this workplace incident for OSHA recordability.

Incident: {row['title']}
Description: {row['description']}
Type: {row['incident_type']}
Severity: {row['severity']}
Injury type: {category_data.get('injury_type', 'unknown')}
Body parts: {category_data.get('body_parts', [])}
Treatment: {category_data.get('treatment', 'unknown')}
Lost days: {category_data.get('lost_days', 0)}

OSHA recordability criteria (29 CFR 1904):
- Death
- Days away from work
- Restricted work or transfer to another job
- Medical treatment beyond first aid
- Loss of consciousness
- Significant injury or illness diagnosed by a physician

Respond in JSON:
{{"recordable": true/false, "classification": "death|days_away|restricted_duty|medical_treatment|loss_of_consciousness|significant_injury|not_recordable", "reasoning": "brief explanation"}}
"""

        settings = get_settings()
        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.analysis_model,
                contents=prompt,
            )
            text = (response.text or "").strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
        except Exception as e:
            logger.error("OSHA AI determination failed: %s", e)
            raise HTTPException(status_code=500, detail="AI determination failed")

        return {
            "incident_id": str(incident_id),
            "recordable": result.get("recordable", False),
            "classification": result.get("classification", "not_recordable"),
            "reasoning": result.get("reasoning", ""),
        }
