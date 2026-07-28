"""OSHA Form 300A annual summary: computed view, admin save/override, and the
PDF + CSV exports. All four gate on the reviewer attestation in `_shared`.
"""
import csv
import io
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir.osha import Osha300ASaveRequest, Osha300ASummary
from app.matcha.routes.ir_incidents._shared import log_audit
from app.matcha.services.ir.naics_titles import naics_industry_description
from ._shared import _active_headcount, _aggregate_300a, _attest_export

logger = logging.getLogger(__name__)

router = APIRouter()


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
    from ._pdf import render_300a_pdf
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
