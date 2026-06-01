"""OSHA log + form endpoints for IR Incidents.

Covers:
- OSHA 300 log (recordable injury/illness log) + CSV
- OSHA 301 form (per-incident detail)
- OSHA 300A annual summary + CSV
- Recordability update (manual)
- Recordability AI determination (Gemini-backed)
"""
import asyncio
import csv
import io
import json
import logging
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
    OshaRecordabilityUpdate,
)
from ._shared import log_audit
from app.core.services.osha_redaction import redact_osha_text
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


def _ita_size_category(avg_employees) -> int:
    """OSHA ITA establishment size code: 1 (<20), 2 (20–249), 3 (>=250)."""
    n = avg_employees or 0
    if n >= 250:
        return 3
    if n >= 20:
        return 2
    return 1


# Mandatory ITA fields that can realistically be missing (city/state/zipcode are
# NOT NULL on business_locations; address/ein/naics/hours are the gaps).
def _missing_ita_fields(est: dict) -> list[str]:
    """Return the list of required ITA fields absent from an establishment dict.

    Pure (no DB) so it can be unit-tested. `est` carries the EIN/NAICS already
    resolved with company-level fallback, plus street_address + total_hours_worked.
    """
    missing = []
    for field in ("ein", "naics", "street_address"):
        val = est.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    if est.get("total_hours_worked") is None:
        missing.append("total_hours_worked")
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


async def _aggregate_300a(conn, company_id, location_id, year) -> dict:
    """Aggregate recordable-incident totals for one establishment in one year.

    Single source of the 300A column math — shared by the summary endpoint, the
    PDF, and the ITA export so the three can never drift. M-column injury/illness
    type lives in osha_form_301_data->>'injury_type'; NULL falls back to 'injury'
    so legacy rows still land in the Standard Injury column.
    """
    return await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total_cases,
            COALESCE(SUM(CASE WHEN osha_classification = 'death' THEN 1 ELSE 0 END), 0) AS total_deaths,
            COALESCE(SUM(CASE WHEN osha_classification = 'days_away' THEN 1 ELSE 0 END), 0) AS total_days_away_cases,
            COALESCE(SUM(CASE WHEN osha_classification = 'restricted_duty' THEN 1 ELSE 0 END), 0) AS total_restricted_cases,
            COALESCE(SUM(CASE WHEN osha_classification NOT IN ('death','days_away','restricted_duty') THEN 1 ELSE 0 END), 0) AS total_other_recordable,
            COALESCE(SUM(days_away_from_work), 0) AS total_days_away,
            COALESCE(SUM(days_restricted_duty), 0) AS total_days_restricted,
            COALESCE(SUM(CASE WHEN COALESCE(osha_form_301_data->>'injury_type','injury') = 'injury' THEN 1 ELSE 0 END), 0) AS total_injuries,
            COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'skin_disorder' THEN 1 ELSE 0 END), 0) AS total_skin_disorders,
            COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'respiratory' THEN 1 ELSE 0 END), 0) AS total_respiratory,
            COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'poisoning' THEN 1 ELSE 0 END), 0) AS total_poisonings,
            COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'hearing_loss' THEN 1 ELSE 0 END), 0) AS total_hearing_loss,
            COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'other_illness' THEN 1 ELSE 0 END), 0) AS total_other_illnesses
        FROM ir_incidents
        WHERE company_id = $1
          AND location_id = $2
          AND osha_recordable = true
          AND EXTRACT(YEAR FROM occurred_at) = $3
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

    entries = []
    for row in rows:
        emp_name = row["reported_by_name"]
        if row["emp_first_name"]:
            emp_name = f"{row['emp_first_name']} {row['emp_last_name'] or ''}".strip()

        category_data = _safe_json_loads(row.get("category_data"), {})
        injury_type = category_data.get("injury_type")

        entries.append(Osha300LogEntry(
            case_number=row["osha_case_number"] or str(row["id"])[:8],
            employee_name=emp_name,
            job_title=row["emp_job_title"],
            date_of_injury=row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else "",
            location=redact_osha_text(row["location"]),
            description=redact_osha_text(row["description"]),
            classification=row["osha_classification"],
            days_away=row["days_away_from_work"],
            days_restricted=row["days_restricted_duty"],
            injury_type=injury_type,
            incident_id=str(row["id"]),
        ))
    return entries


@router.get("/osha/300-log/csv")
async def get_osha_300_log_csv(
    year: int = Query(..., description="Calendar year for the 300 log CSV"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300 log as CSV for a given year."""
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


@router.get("/osha/301/{incident_id}")
async def get_osha_301_form(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 301 form data for a specific recordable incident."""
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

    category_data = _safe_json_loads(row.get("category_data"), {})
    form_301_data = _safe_json_loads(row.get("osha_form_301_data"), {})

    emp_name = row["reported_by_name"]
    if row["emp_first_name"]:
        emp_name = f"{row['emp_first_name']} {row['emp_last_name'] or ''}".strip()

    # Redact PII / patient PHI from free-text fields. Injury structure
    # (injury_type, body_parts, classification) is passed through unredacted
    # so the 301 still describes the injury.
    return {
        "incident_id": str(row["id"]),
        "case_number": row["osha_case_number"] or str(row["id"])[:8],
        "employee_name": emp_name,
        "employee_email": row.get("emp_email"),
        "employee_job_title": row.get("emp_job_title"),
        "employee_start_date": row["emp_start_date"].isoformat() if row.get("emp_start_date") else None,
        "employer_name": row.get("company_name"),
        "employer_address": row.get("company_address"),
        "establishment_name": row.get("location_name"),
        "establishment_city": row.get("location_city"),
        "establishment_state": row.get("location_state"),
        "date_of_injury": row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else None,
        "time_of_event": row["occurred_at"].strftime("%H:%M") if row["occurred_at"] else None,
        "location_of_event": redact_osha_text(row.get("location")),
        "description_of_injury": redact_osha_text(row.get("description")),
        "object_or_substance": category_data.get("equipment_involved"),
        "injury_type": category_data.get("injury_type"),
        "body_parts_affected": category_data.get("body_parts", []),
        "treatment": redact_osha_text(category_data.get("treatment")),
        "osha_classification": row.get("osha_classification"),
        "days_away_from_work": row.get("days_away_from_work") or 0,
        "days_restricted_duty": row.get("days_restricted_duty") or 0,
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
    current_user=Depends(require_admin_or_client),
):
    """Render the faithful federal OSHA Form 300A as a PDF for one establishment."""
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
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300A annual summary as CSV."""
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

    problems = []
    for est in establishments:
        missing = _missing_ita_fields(est)
        if missing:
            problems.append({
                "location_id": est["location_id"],
                "establishment_name": est["establishment_name"],
                "missing": missing,
            })
    return problems


@router.get("/osha/ita/export.csv")
async def export_ita_csv(
    year: int = Query(..., description="Calendar year for the ITA bulk export"),
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
            "ein": est["ein"] or "",
            "company_name": est["company_name"],
            "establishment_name": est["establishment_name"],
            "street_address": est["street_address"] or "",
            "city": est["city"] or "",
            "state": est["state"] or "",
            "zip_code": est["zip_code"] or "",
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

        updated = await conn.fetchrow(
            f"UPDATE ir_incidents SET {', '.join(sets)} WHERE id = $1 AND company_id = $2 RETURNING *",
            *params,
        )
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
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-3-flash-preview")
            response = await asyncio.to_thread(
                model.generate_content, prompt
            )
            text = response.text.strip()
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
